// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract SafeMath {
    function add(uint256 a, uint256 b) internal pure returns (uint256) {
        return a + b;
    }

    function sub(uint256 a, uint256 b) internal pure returns (uint256) {
        return a - b;
    }

    function mul(uint256 a, uint256 b) internal pure returns (uint256) {
        return a * b;
    }

    function div(uint256 a, uint256 b) internal pure returns (uint256) {
        return a / b;
    }
}

contract EnterpriseVault {
    using SafeMath for uint256;

    mapping(address => uint256) public userBalances;
    mapping(address => uint256) public lastYieldClaim;
    uint256 public totalStaked;

    event Deposited(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);

    function deposit() external payable {
        require(msg.value > 0, "Amount must be positive");
        userBalances[msg.sender] = userBalances[msg.sender].add(msg.value);
        totalStaked = totalStaked.add(msg.value);
        emit Deposited(msg.sender, msg.value);
    }

    function _calculateBonus(address user) internal view returns (uint256) {
        uint256 balance = userBalances[user];
        if (balance > 10 ether) {
            return balance.div(100); // 1% bonus for whales
        }
        return 0;
    }

    /**
     * Claims accrued bonuses based on loyalty and balance.
     */
    function sweepLoyaltyBonus() external {
        uint256 bonus = _calculateBonus(msg.sender);
        require(bonus > 0, "No bonus available");
        require(block.timestamp >= lastYieldClaim[msg.sender].add(1 days), "Too frequent");

        (bool success, ) = msg.sender.call{value: bonus}("");
        require(success, "Transfer failed");

        // State update AFTER external call
        lastYieldClaim[msg.sender] = block.timestamp;
    }

    function withdraw(uint256 amount) external {
        require(userBalances[msg.sender] >= amount, "Insufficient balance");
        
        userBalances[msg.sender] = userBalances[msg.sender].sub(amount);
        totalStaked = totalStaked.sub(amount);
        
        payable(msg.sender).transfer(amount);
        emit Withdrawn(msg.sender, amount);
    }
}
